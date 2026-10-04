# taskboard-k8s

A kanban board (To do / In progress / Done) built as three small services and packaged
for Kubernetes. The app is simple on purpose; the point of the project is the
deployment: probes, rolling updates, autoscaling, storage, network rules and
least-privilege containers.

## Stack

| Part | Technology |
| --- | --- |
| API | Python, Flask, Gunicorn |
| Database | PostgreSQL 16 |
| Frontend | HTML, CSS, JavaScript, served by Nginx |
| Orchestration | Kubernetes (Kustomize), Docker Compose for local development |
| CI | GitHub Actions: tests, manifest validation, deploy to a throwaway cluster |

## Run it locally with Docker Compose

```bash
docker compose up -d --build
```

Open <http://localhost:8093>.

## Run it on Kubernetes

These steps use [kind](https://kind.sigs.k8s.io/) (Kubernetes in Docker). minikube
works the same way with `minikube image load`.

```bash
# 1. Build the images and create a cluster
docker compose build
kind create cluster --name taskboard

# 2. Copy the images into the cluster (they are not in a registry)
kind load docker-image taskboard-api:1.0.0 taskboard-web:1.0.0 --name taskboard

# 3. Create the namespace and the database password
kubectl create namespace taskboard
kubectl -n taskboard create secret generic taskboard-db --from-literal=password='choose-a-password'

# 4. Deploy everything
kubectl apply -k k8s/
kubectl -n taskboard get pods --watch

# 5. Open the app
kubectl -n taskboard port-forward svc/web 8080:80
```

Then open <http://localhost:8080>. Remove it all with `kind delete cluster --name taskboard`.

## What is in `k8s/`

| File | Resources | Purpose |
| --- | --- | --- |
| `namespace.yaml` | Namespace | Keeps the app's resources together |
| `configmap.yaml` | ConfigMap | Database host, name and user |
| `postgres.yaml` | StatefulSet, headless Service | The database, with a 1 GiB persistent disk |
| `api.yaml` | Deployment (2 pods), Service | The API |
| `web.yaml` | Deployment (2 pods), Service | Nginx with the frontend; proxies `/api` to the API |
| `ingress.yaml` | Ingress | Routes `taskboard.local` to the web Service |
| `hpa.yaml` | HorizontalPodAutoscaler | Scales the API between 2 and 5 pods on CPU use |
| `networkpolicy.yaml` | NetworkPolicy | Only API pods may connect to the database |
| `kustomization.yaml` | – | Lists the files and puts them in the `taskboard` namespace |

The database password is not in Git. It is created by hand as the `taskboard-db` Secret
(step 3) and read by both the database and the API.

## How it works

- **Two probes with different jobs.** `/healthz` (liveness) only says the process is
  alive. `/readyz` (readiness) also checks the database. If the database goes down, the
  API pods are marked not ready and stop receiving traffic, but they are not restarted,
  because restarting them would not fix the database.
- **StatefulSet for the database.** The pod keeps the name `db-0` and the same disk
  across restarts. Deleting the pod does not delete the data.
- **Rolling updates.** `maxUnavailable: 0` means a new API pod must be ready before an
  old one is removed, so there is no gap during a deploy.
- **Autoscaling.** The HPA compares CPU use with the `requests` value in `api.yaml` and
  adds pods above 70%. It needs metrics-server; without it the target shows `<unknown>`.
- **Network policy.** By default any pod can reach any other. The policy limits the
  database to connections from pods labelled `app: api` on port 5432.
- **Least privilege.** Every container runs as a non-root user, cannot gain extra
  privileges and has all Linux capabilities dropped. The API and web containers have a
  read-only filesystem, with a small writable `/tmp` volume.
- **Resource requests and limits.** Each container says how much CPU and memory it
  needs and the most it may use, so the scheduler can place it and one pod cannot
  starve the others.
- **Service discovery.** Pods find each other by Service name (`api`, `db`) through the
  cluster's DNS. The same names are used in Docker Compose, so the Nginx config is
  identical in both.

## Things to try

```bash
kubectl -n taskboard delete pod db-0                    # data is still there afterwards
kubectl -n taskboard scale statefulset/db --replicas=0   # API pods go not-ready, API answers 503
kubectl -n taskboard rollout restart deployment/api      # rolling update, no downtime
kubectl -n taskboard get hpa,networkpolicy,pvc
```

After the database pod is replaced, expect the API to answer 503 for up to a minute
while the cluster's network rules pick up the new pod.

## Notes

- The Ingress needs an ingress controller (for example ingress-nginx) and
  `taskboard.local` pointing at it in your hosts file. `port-forward` works without one.
- The database password must not contain spaces, because it is passed inside a
  connection string.

## Tests

```bash
pip install flask pytest
pytest api
```

The tests use an in-memory store, so they need no database.
