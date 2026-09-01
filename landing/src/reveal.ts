/** Fades in every [data-reveal] element the first time it enters the viewport. */
export function initScrollReveal(root: ParentNode = document): void {
  const targets = Array.from(root.querySelectorAll<HTMLElement>("[data-reveal]"));
  const reduceMotion = window.matchMedia?.("(prefers-reduced-motion: reduce)").matches === true;

  if (!("IntersectionObserver" in window) || reduceMotion) {
    targets.forEach((el) => el.classList.add("in-view"));
    return;
  }

  const observer = new IntersectionObserver(
    (entries) => {
      for (const entry of entries) {
        if (entry.isIntersecting) {
          entry.target.classList.add("in-view");
          observer.unobserve(entry.target);
        }
      }
    },
    { threshold: 0.12, rootMargin: "0px 0px -60px 0px" },
  );

  targets.forEach((el) => observer.observe(el));
}
