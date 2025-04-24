const express = require("express");
const request = require("request");
const cheerio = require("cheerio");

const app = express();
const PORT = 7070;
const BASE_URL = "https://timeforms.app";

app.use((req, res) => {
  const targetUrl = BASE_URL + req.originalUrl;

  request(targetUrl, (error, response, body) => {
    if (error || response.statusCode !== 200) {
      return res.status(500).send("Error loading target page.");
    }

    const contentType = response.headers["content-type"] || "";

    // If it's HTML, inject custom CSS
    if (contentType.includes("text/html")) {
      const $ = cheerio.load(body);

      // Inject CSS to hide the elements
      $("body").append(`
            <style>
              .fixed.top-8.left-8.text-2xl {
                display: none !important;
              }
              .fixed.bottom-8.left-8.text-xs {
                display: none !important;
              }
              .fixed.left-8.top-1\/2.-translate-y-1\/2 {
                display: none !important;
              }
              .fixed.left-8.z-50 {
                display: none !important;
              }
              .fixed.bottom-0.left-0.right-0.w-full.z-50 {
                display: none !important;
              }
            </style>
          `);

      res.set("Content-Type", "text/html");
      return res.send($.html());
    }

    // Otherwise (CSS, JS, etc.), just pipe it directly
    request(targetUrl).pipe(res);
  });
});

app.listen(PORT, () => {
  console.log(`Proxy running at http://localhost:${PORT}`);
});
