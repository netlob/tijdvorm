// const express = require("express");
// const request = require("request");
// const cheerio = require("cheerio");

// const app = express();
// const PORT = 8080;

// app.get("/", (req, res) => {
//   const targetUrl = "https://timeforms.app/";

//   request(targetUrl, (error, response, body) => {
//     if (error || response.statusCode !== 200) {
//       return res.status(500).send("Error loading Timeforms");
//     }

//     const $ = cheerio.load(body);

//     // 🧠 Inject your custom JavaScript here
//     // $("body").append(`
//     //   <script>
//     //     // Custom JS goes here — example:
//     //     const interval = setInterval(() => {
//     //       const ui = document.querySelector('#root > div.w-full.min-h-screen.flex.items-center.justify-center > ');
//     //       if (ui) {
//     //         ui.style.display = "none";
//     //         clearInterval(interval);
//     //       }
//     //     }, 500);
//     //   </script>
//     // `);

//     $("head").append(`
//         <style>
//           /* Hide everything except the main centered artwork container */
//           body * {
//             display: none !important;
//           }

//           #root > div.w-full.min-h-screen.flex.items-center.justify-center {
//             display: flex !important;
//           }
//         </style>
//       `);

//     res.send($.html());
//   });
// });

// app.listen(PORT, () => {
//   console.log(`Proxy running on http://localhost:${PORT}`);
// });

const express = require("express");
const request = require("request");
const cheerio = require("cheerio");

const app = express();
const PORT = 8080;
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

      //   body * {
      //     display: none !important;
      //   }
      //   #root > div.w-full.min-h-screen.flex.items-center.justify-center {
      //     display: flex !important;
      //   }
      $("body").append(`
            <style>
            #root > div > div {
             display: none !important;
            }
             #root > div > div.max-w-[92%] {
             display: block !important;
             }
              #root > div > div.flex {
                  display: flex !important;
              }
            //   .max-w-[92%] {
            //       max-width: 100% !important;
            //   }
            .h-[85vh] .max-h-[85vh] {
              height: 100vh !important;
              max-height: 100vh !important;
            }
              .inset-[24px] {
                  top: 0px !important;
                  bottom: 0px !important;
                  left: 0px !important;
                  right: 0px !important;
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
