(() => {
  const properties = [
    "fontFamily",
    "fontSize",
    "fontWeight",
    "fontStyle",
    "fontStretch",
    "fontVariant",
    "fontKerning",
    "fontFeatureSettings",
    "fontVariationSettings",
    "fontOpticalSizing",
    "lineHeight",
    "letterSpacing",
    "wordSpacing",
    "textIndent",
    "textTransform",
    "whiteSpace",
    "overflowWrap",
    "wordBreak",
    "hyphens",
    "tabSize",
    "direction",
    "unicodeBidi",
    "lineBreak",
    "textRendering",
  ];
  const scheduled = new WeakSet();
  function align(area) {
    scheduled.delete(area);
    const editor = area.parentElement,
      gutter = editor.querySelector(".line-numbers pre");
    if (!gutter) return;
    const style = getComputedStyle(area),
      lineHeight = parseFloat(style.lineHeight),
      width =
        area.clientWidth -
        parseFloat(style.paddingLeft) -
        parseFloat(style.paddingRight);
    if (width <= 0) return;
    const mirror = document.createElement("div");
    Object.assign(mirror.style, {
      position: "fixed",
      left: "-100000px",
      top: "0",
      width: width + "px",
      visibility: "hidden",
      margin: "0",
    });
    for (const property of properties) mirror.style[property] = style[property];
    for (const value of area.value.split("\n")) {
      const row = document.createElement("div");
      row.textContent = value || "\u200b";
      mirror.append(row);
    }
    document.body.append(mirror);
    gutter.replaceChildren();
    for (const [index, row] of [...mirror.children].entries()) {
      const number = document.createElement("div");
      number.textContent = index + 1;
      number.style.height =
        Math.max(lineHeight, row.getBoundingClientRect().height) + "px";
      number.style.lineHeight = style.lineHeight;
      gutter.append(number);
    }
    mirror.remove();
    gutter.style.transform = "translateY(" + -area.scrollTop + "px)";
  }
  function schedule(area) {
    if (scheduled.has(area)) return;
    scheduled.add(area);
    requestAnimationFrame(() => align(area));
  }
  for (const area of document.querySelectorAll(".markdown-input")) {
    const editor = area.parentElement,
      highlight = area.previousElementSibling;
    area.addEventListener("input", () => schedule(area));
    area.addEventListener("scroll", () => schedule(area));
    editor
      .closest(".manual-section")
      ?.querySelector(".word-wrap")
      ?.addEventListener("change", () => schedule(area));
    new ResizeObserver(() => schedule(area)).observe(area);
    new MutationObserver(() => schedule(area)).observe(highlight, {
      childList: true,
      subtree: true,
      characterData: true,
    });
    schedule(area);
  }
  if (document.fonts?.ready)
    document.fonts.ready.then(() =>
      document.querySelectorAll(".markdown-input").forEach(schedule),
    );
})();
