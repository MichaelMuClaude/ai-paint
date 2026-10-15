// Trace a raw RGBA image into an SVG with ImageTracer. Part of ai-paint (MIT).
// Usage: node trace_svg.js input.raw width height output.svg
const fs = require("fs");
const path = require("path");
const ImageTracer = require(path.join(__dirname, "imagetracer.js"));

const [input, width, height, output] = process.argv.slice(2);
const data = new Uint8ClampedArray(fs.readFileSync(input));
const options = {
  numberofcolors: 2,
  colorsampling: 0,
  pathomitting: 12,
  ltres: 1,
  qtres: 1,
  roundcoords: 1,
  scale: 1,
  strokewidth: 0,
  viewbox: true,
};
const svg = ImageTracer.imagedataToSVG({ width: Number(width), height: Number(height), data }, options);
fs.writeFileSync(output, svg);
