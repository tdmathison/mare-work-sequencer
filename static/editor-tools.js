(() => {
  const form = document.getElementById("report-form");
  if (!form) return;
  const cid = form.dataset.caseId,
    status = {
      set textContent(value) {
        document
          .querySelectorAll("#report-save-status,[data-editor-status]")
          .forEach((node) => (node.textContent = value));
      },
    };
  async function request(url, data) {
    const response = await fetch(
      url,
      data ? { method: "POST", body: data } : {},
    );
    const result = await response.json();
    if (!response.ok) throw Error(result.error || "Image request failed");
    return result;
  }
  function insert(area, text) {
    area.setRangeText(text, area.selectionStart, area.selectionEnd, "end");
    area.focus();
    area.dispatchEvent(new Event("input"));
  }
  async function images() {
    const result = await request("/cases/" + cid + "/report-images");
    for (const section of document.querySelectorAll(".manual-section")) {
      const area = section.querySelector(".markdown-input"),
        list = section.querySelector(".report-image-list");
      list.replaceChildren();
      for (const image of result.images.filter(
        (item) => item.section === (area.dataset.imageSection || area.name),
      )) {
        const row = document.createElement("div"),
          link = document.createElement("a"),
          remove = document.createElement("button");
        link.href = "/cases/" + cid + "/report-images/" + image.name;
        link.target = "_blank";
        link.rel = "noopener";
        link.textContent = image.name;
        remove.type = "button";
        remove.textContent = "X";
        remove.setAttribute("aria-label", "Delete image " + image.name);
        remove.addEventListener("click", async () => {
          if (
            !confirm(
              "Delete this image from the MIP and remove its Markdown references?",
            )
          )
            return;
          try {
            const data = new FormData();
            data.set("csrf", form.elements.csrf.value);
            await request(
              "/cases/" + cid + "/report-images/" + image.name + "/delete",
              data,
            );
            for (const editor of document.querySelectorAll(".markdown-input")) {
              editor.value = editor.value.replace(
                new RegExp(
                  "!\\[[^\\]]*\\]\\(assets/" +
                    image.name.replace(".", "\\.") +
                    "\\)",
                  "g",
                ),
                "",
              );
              editor.dispatchEvent(new Event("input"));
            }
            await images();
          } catch (e) {
            status.textContent = e.message;
          }
        });
        row.append(link, remove);
        list.append(row);
      }
    }
  }
  async function upload(section, files) {
    const area = section.querySelector(".markdown-input");
    for (const file of files) {
      const data = new FormData();
      data.set("csrf", form.elements.csrf.value);
      data.set("section", area.dataset.imageSection || area.name);
      data.set("image", file);
      status.textContent = "Saving image…";
      const result = await request("/cases/" + cid + "/report-images", data);
      insert(
        area,
        "\n::: figure\n![Image](" +
          result.markdown_url +
          ")\n\n*Figure " +
          result.figure +
          ":* \n:::\n",
      );
    }
    await images();
    status.textContent =
      "Image saved. Save report sections to retain its Markdown reference.";
  }
  for (const section of document.querySelectorAll(".manual-section")) {
    const area = section.querySelector(".markdown-input"),
      gutter = section.querySelector(".line-numbers pre"),
      picker = section.querySelector(".markdown-image-input");
    function lines() {
      const editor = area.parentElement,
        wrap = section.querySelector(".word-wrap").checked;
      editor.classList.toggle("wrap-on", wrap);
      area.wrap = wrap ? "soft" : "off";
      const style = getComputedStyle(area),
        height = parseFloat(style.lineHeight),
        width =
          area.clientWidth -
          parseFloat(style.paddingLeft) -
          parseFloat(style.paddingRight);
      gutter.replaceChildren();
      if (width <= 0) return;
      const mirror = document.createElement("div");
      Object.assign(mirror.style, {
        position: "fixed",
        left: "-100000px",
        top: "0",
        width: width + "px",
        font: style.font,
        lineHeight: style.lineHeight,
        whiteSpace: wrap ? "pre-wrap" : "pre",
        overflowWrap: "break-word",
        tabSize: "4",
        visibility: "hidden",
      });
      const values = area.value.split("\n");
      for (const value of values) {
        const row = document.createElement("div");
        row.textContent = value || "\u200b";
        mirror.append(row);
      }
      document.body.append(mirror);
      [...mirror.children].forEach((row, index) => {
        const number = document.createElement("div");
        number.textContent = index + 1;
        number.style.height =
          Math.max(height, row.getBoundingClientRect().height) + "px";
        gutter.append(number);
      });
      mirror.remove();
      gutter.style.transform = "translateY(" + -area.scrollTop + "px)";
    }
    section.querySelector(".word-wrap").addEventListener("change", () => {
      lines();
      area.dispatchEvent(new Event("scroll"));
    });
    new ResizeObserver(lines).observe(area);
    area.addEventListener("input", lines);
    area.addEventListener("scroll", lines);
    new MutationObserver(lines).observe(area.previousElementSibling, {
      childList: true,
      subtree: true,
    });
    lines();
    picker.addEventListener("change", () =>
      upload(section, picker.files).catch(
        (e) => (status.textContent = e.message),
      ),
    );
    area.addEventListener("dragover", (event) => {
      if (!area.closest("fieldset:disabled")) event.preventDefault();
    });
    area.addEventListener("drop", (event) => {
      if (area.closest("fieldset:disabled")) return;
      event.preventDefault();
      upload(section, event.dataTransfer.files).catch(
        (e) => (status.textContent = e.message),
      );
    });
    section
      .querySelector(".markdown-block-style")
      .addEventListener("change", (event) => {
        const kind = event.target.value,
          start = area.value.lastIndexOf("\n", area.selectionStart - 1) + 1;
        let end = area.value.indexOf("\n", area.selectionEnd);
        if (end < 0) end = area.value.length;
        let text = area.value
          .slice(start, end)
          .split("\n")
          .map((line) => line.replace(/^(?:#{1,6} | > |> )/, ""));
        if (kind.startsWith("h"))
          text = text.map(
            (line) => "#".repeat(Number(kind.slice(1))) + " " + line,
          );
        else if (kind === "quote") text = text.map((line) => "> " + line);
        area.setSelectionRange(start, end);
        insert(
          area,
          kind === "code"
            ? "\n" +
                String.fromCharCode(96).repeat(3) +
                "\n" +
                text.join("\n") +
                "\n" +
                String.fromCharCode(96).repeat(3) +
                "\n"
            : text.join("\n"),
        );
      });
    for (const button of section.querySelectorAll("[data-md]"))
      button.addEventListener("click", () => {
        button.closest(".markdown-menu")?.removeAttribute("open");
        const selected = area.value.slice(
          area.selectionStart,
          area.selectionEnd,
        );
        switch (button.dataset.md) {
          case "italic":
            insert(area, "*" + (selected || "italic text") + "*");
            break;
          case "bold":
            insert(area, "**" + (selected || "bold text") + "**");
            break;
          case "url":
            insert(
              area,
              "[" + (selected || "link text") + "](https://example.com)",
            );
            break;
          case "bullet":
            insert(
              area,
              "\n" +
                (selected || "List item")
                  .split("\n")
                  .map((line) => "- " + line)
                  .join("\n") +
                "\n",
            );
            break;
          case "table":
            insert(
              area,
              "\n| Column 1 | Column 2 |\n| --- | --- |\n| Value | Value |\n\n",
            );
            break;
          case "align-left":
          case "align-center":
          case "align-right": {
            const start =
              area.value.lastIndexOf("\n", area.selectionStart - 1) + 1;
            let end = area.value.indexOf("\n", area.selectionEnd);
            if (end < 0) end = area.value.length;
            const content = area.value.slice(start, end);
            area.setSelectionRange(start, end);
            insert(
              area,
              "\n::: " + button.dataset.md + "\n" + content + "\n:::\n",
            );
            break;
          }
          case "image":
            picker.value = "";
            picker.click();
            break;
        }
      });
  }
  document.querySelectorAll(".markdown-menu").forEach((menu) =>
    menu.addEventListener("toggle", () => {
      if (menu.open)
        menu
          .closest(".manual-section")
          .querySelectorAll(".markdown-menu")
          .forEach((other) => {
            if (other !== menu) other.open = false;
          });
    }),
  );
  document.addEventListener("click", (event) => {
    if (!event.target.closest(".markdown-menu"))
      document
        .querySelectorAll(".markdown-menu[open]")
        .forEach((menu) => (menu.open = false));
  });
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape") {
      const menus = [...document.querySelectorAll(".markdown-menu[open]")];
      if (menus.length) {
        event.preventDefault();
        event.stopPropagation();
        menus.forEach((menu) => (menu.open = false));
      }
    }
  });
  images().catch((e) => (status.textContent = e.message));
})();
