// Better than .click() - This mimics a real user interaction
export const humanClick = (element: HTMLElement) => {
  const box = element.getBoundingClientRect();
  const x = box.left + (box.right - box.left) / 2;
  const y = box.top + (box.bottom - box.top) / 2;

  const events = ["mousedown", "mouseup", "click"];
  
  events.forEach((eventName) => {
    const event = new MouseEvent(eventName, {
      view: window,
      bubbles: true,
      cancelable: true,
      clientX: x,
      clientY: y,
      button: 0, // Left click
    });
    element.dispatchEvent(event);
  });
  
  console.log("RUTE: Human-simulated click executed.");
};
