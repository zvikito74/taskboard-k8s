const STATUSES = ["todo", "doing", "done"];
const form = document.getElementById("add-form");
const errorEl = document.getElementById("error");
const columns = [...document.querySelectorAll(".column")];

async function api(path, method = "GET", body) {
  const response = await fetch(path, {
    method,
    headers: body ? { "Content-Type": "application/json" } : {},
    body: body ? JSON.stringify(body) : undefined,
  });
  if (!response.ok) throw new Error("request failed: " + response.status);
  return response.status === 204 ? null : response.json();
}

function button(label, className, onClick) {
  const node = document.createElement("button");
  node.textContent = label;
  if (className) node.className = className;
  node.addEventListener("click", onClick);
  return node;
}

async function move(task, status) {
  await api("/api/tasks/" + task.id, "PATCH", { status });
  refresh();
}

function renderTask(task) {
  const item = document.createElement("li");
  item.className = "task";
  item.draggable = true;
  item.addEventListener("dragstart", (event) => event.dataTransfer.setData("text/plain", String(task.id)));

  const title = document.createElement("span");
  title.className = "task-title";
  title.textContent = task.title;

  const actions = document.createElement("div");
  actions.className = "task-actions";
  const position = STATUSES.indexOf(task.status);
  if (position > 0) actions.append(button("←", "", () => move(task, STATUSES[position - 1])));
  if (position < STATUSES.length - 1) actions.append(button("→", "", () => move(task, STATUSES[position + 1])));
  actions.append(button("Delete", "delete", async () => {
    await api("/api/tasks/" + task.id, "DELETE");
    refresh();
  }));

  item.append(title, actions);
  return item;
}

async function refresh() {
  try {
    const tasks = await api("/api/tasks");
    for (const column of columns) {
      const mine = tasks.filter((task) => task.status === column.dataset.status);
      column.querySelector(".tasks").replaceChildren(...mine.map(renderTask));
      column.querySelector(".count").textContent = mine.length;
    }
    errorEl.hidden = true;
  } catch (error) {
    errorEl.hidden = false;
  }
}

// Drag a card onto a column to move it
for (const column of columns) {
  column.addEventListener("dragover", (event) => {
    event.preventDefault();
    column.classList.add("over");
  });
  column.addEventListener("dragleave", () => column.classList.remove("over"));
  column.addEventListener("drop", async (event) => {
    event.preventDefault();
    column.classList.remove("over");
    const id = event.dataTransfer.getData("text/plain");
    if (id) await move({ id }, column.dataset.status);
  });
}

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  await api("/api/tasks", "POST", { title: form.elements.title.value });
  form.reset();
  refresh();
});

refresh();
setInterval(refresh, 10000);
