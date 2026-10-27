// Front end for the /ask API. No framework, no build step.

const API_URL = "https://ku2jdwqc50.execute-api.us-east-1.amazonaws.com/ask";

const form = document.getElementById("ask-form");
const input = document.getElementById("question");
const button = document.getElementById("ask-button");
const tickets = document.getElementById("tickets");
const intro = document.getElementById("intro");
const served = document.getElementById("served");

let number = 0;

const pad = (n) => String(n).padStart(2, "0");

function el(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}

// Answers come back with a little Markdown: **bold**, lists and links.
// Everything is built with textContent, never innerHTML, so nothing in an
// answer can run as code on the page.
const INLINE = /\*\*(.+?)\*\*|\[([^\]]+)\]\((https?:\/\/[^)\s]+)\)|(https?:\/\/[^\s)]+)/g;

function addInline(parent, text) {
  let last = 0;
  for (const match of text.matchAll(INLINE)) {
    parent.append(text.slice(last, match.index));
    if (match[1]) {
      parent.append(el("strong", null, match[1]));
    } else {
      const link = el("a", null, match[2] || match[4]);
      link.href = match[3] || match[4];
      link.rel = "noopener";
      link.target = "_blank";
      parent.append(link);
    }
    last = match.index + match[0].length;
  }
  parent.append(text.slice(last));
}

function renderAnswer(text) {
  const box = document.createDocumentFragment();
  let list = null;

  for (const raw of text.split("\n")) {
    const line = raw.trim();
    const bullet = line.match(/^[-*]\s+(.*)/);
    const numbered = line.match(/^\d+\.\s+(.*)/);

    if (bullet || numbered) {
      const tag = bullet ? "ul" : "ol";
      if (!list || list.tagName.toLowerCase() !== tag) {
        list = el(tag);
        box.append(list);
      }
      const item = el("li");
      addInline(item, (bullet || numbered)[1]);
      list.append(item);
      continue;
    }

    list = null;
    if (line) {
      const p = el("p");
      addInline(p, line);
      box.append(p);
    }
  }
  return box;
}

function formatDate(iso) {
  const date = new Date(`${iso}T00:00:00`);
  if (Number.isNaN(date.getTime())) return iso;
  return date.toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric" });
}

function newTicket(question) {
  number += 1;
  const ticket = el("li", "ticket");
  const head = el("div", "ticket-head");
  head.append(el("span", "number", `No. ${pad(number)}`), el("span", null, question));
  ticket.append(head);
  return ticket;
}

function fillTicket(ticket, data) {
  const body = el("div", "ticket-body");

  if (!data.grounded) {
    ticket.classList.add("muted");
    body.append(el("p", "status", "Not answered"));
  }
  body.append(renderAnswer(data.answer || ""));
  ticket.append(body);

  if (data.sources && data.sources.length) {
    const foot = el("div", "ticket-foot");
    for (const source of data.sources) {
      const dl = el("dl", "source");
      const link = el("a", null, source.title || source.id);
      link.href = source.url;
      link.rel = "noopener";
      link.target = "_blank";
      const title = el("dd");
      title.append(link);
      dl.append(el("dt", null, "Source"), title);
      if (source.last_checked) {
        dl.append(el("dt", null, "Checked"), el("dd", null, formatDate(source.last_checked)));
      }
      foot.append(dl);
    }
    ticket.append(foot);
  }
}

function showError(ticket, status) {
  ticket.remove();
  number -= 1;
  const message = status === 429
    ? "Too many people at the counter right now. Try again in a moment."
    : "Couldn't reach the counter. Check your connection and try again.";
  tickets.append(el("li", "error", message));
}

async function ask(question) {
  intro.hidden = true;
  document.body.classList.add("started");
  button.disabled = true;

  const ticket = newTicket(question);
  const waiting = el("p", "waiting ticket-body", `Calling No. ${pad(number)}`);
  ticket.append(waiting);
  tickets.append(ticket);
  ticket.scrollIntoView({ behavior: "smooth", block: "nearest" });

  try {
    const response = await fetch(API_URL, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ question }),
    });
    if (!response.ok) {
      showError(ticket, response.status);
      return;
    }
    const data = await response.json();
    waiting.remove();
    fillTicket(ticket, data);
    served.textContent = pad(number);
  } catch {
    showError(ticket);
  } finally {
    button.disabled = false;
    input.focus();
  }
}

form.addEventListener("submit", (event) => {
  event.preventDefault();
  const question = input.value.trim();
  if (!question) return;
  input.value = "";
  ask(question);
});

for (const example of document.querySelectorAll(".example")) {
  example.addEventListener("click", () => ask(example.textContent));
}
