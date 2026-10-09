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
    window.MareEditors.get(area).insert(text);
  }
  async function images() {
    const result = await request("/cases/" + cid + "/report-images");
    for (const section of document.querySelectorAll(".manual-section")) {
      const area = section.querySelector(".markdown-source"),
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
            for (const editor of document.querySelectorAll(".markdown-source")) {
              window.MareEditors.get(editor).replaceMatches(
                new RegExp(
                  "!\\[[^\\]]*\\]\\(assets/" +
                    image.name.replace(/\./g, "\\.") +
                    "\\)",
                  "g",
                ),
              );
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
    const area = section.querySelector(".markdown-source");
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
    const area = section.querySelector(".markdown-source"),
      picker = section.querySelector(".markdown-image-input");
    area.addEventListener("markdown-images", (event) =>
      upload(section, event.detail.files).catch((error) => (status.textContent = error.message)),
    );
    picker.addEventListener("change", () =>
      upload(section, picker.files).catch(
        (e) => (status.textContent = e.message),
      ),
    );
  }
  images().catch((e) => (status.textContent = e.message));
})();
