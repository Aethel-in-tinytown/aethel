/** Bundle split ES modules and publish an HTML entry with fingerprinted assets. */
import * as esbuild from "esbuild";
import { cp, mkdir, readFile, writeFile, readdir, rm } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import http from "node:http";
import net from "node:net";
import { gzipSync } from "node:zlib";
const root = path.dirname(fileURLToPath(import.meta.url));
const outdir = path.join(root, "dist");
const serve = process.argv.includes("--serve");
const backend = new URL(
  process.env.AETHEL_DEV_BACKEND ?? "http://127.0.0.1:8080",
);
const entry = await readFile(path.join(root, "index.html"), "utf8");
const publish = {
  name: "publish-entry",
  setup(build) {
    build.onEnd(async (result) => {
      if (result.errors.length) return;
      await mkdir(outdir, { recursive: true });
      const outputs = Object.entries(result.metafile.outputs);
      const [js, info] = outputs.find(([, v]) =>
        v.entryPoint?.endsWith("src/main.tsx"),
      );
      const css = info.cssBundle;
      const relative = (value) =>
        "/" +
        path
          .relative(outdir, path.resolve(root, value))
          .split(path.sep)
          .join("/");
      await writeFile(
        path.join(outdir, "index.html"),
        entry
          .replace("/main.js", relative(js))
          .replace("/main.css", relative(css)),
      );
      await cp(
        path.join(root, "assets/favicon.ico"),
        path.join(outdir, "favicon.ico"),
      );
      const fonts = path.join(root, "assets/fonts");
      for (const name of await readdir(fonts))
        if (name.endsWith("-OFL.txt"))
          await cp(path.join(fonts, name), path.join(outdir, "assets", name));
      if (!serve) {
        // Compress text assets once at build time, not on every spectator request.
        for (const output of Object.keys(result.metafile.outputs))
          if (/\.(js|css)$/.test(output)) {
            const target = path.resolve(root, output);
            await writeFile(
              target + ".gz",
              gzipSync(await readFile(target), { level: 9 }),
            );
          }
        await cp(outdir, path.join(root, "../aethel_web/static"), {
          recursive: true,
        });
      }
    });
  },
};
const options = {
  absWorkingDir: root,
  entryPoints: ["src/main.tsx"],
  bundle: true,
  outdir,
  format: "esm",
  splitting: true,
  metafile: true,
  entryNames: "[name]-[hash]",
  chunkNames: "chunks/[name]-[hash]",
  target: ["es2020", "chrome100", "safari16"],
  jsx: "automatic",
  jsxImportSource: "preact",
  loader: { ".woff2": "file", ".css": "css" },
  assetNames: "assets/[name]-[hash]",
  minify: !serve,
  sourcemap: serve ? "inline" : false,
  logLevel: "info",
  plugins: [publish],
};
if (!serve) {
  await rm(outdir, { recursive: true, force: true });
  await rm(path.join(root, "../aethel_web/static"), {
    recursive: true,
    force: true,
  });
  await esbuild.build(options);
} else {
  const context = await esbuild.context(options);
  await context.watch();
  await context.serve({ servedir: outdir, host: "127.0.0.1", port: 8083 });
  // Browser requests stay same-origin; development forwards HTTP and WS to Python.
  const server = http.createServer((request, response) => {
    const api =
      request.url.startsWith("/api/") || request.url.startsWith("/health/");
    const target = api ? backend : new URL("http://127.0.0.1:8083");
    const headers = { ...request.headers, host: target.host };
    if (api && headers.origin) headers.origin = backend.origin;
    const proxy = http.request(
      {
        hostname: target.hostname,
        port: target.port,
        method: request.method,
        path: request.url,
        headers,
      },
      (upstream) => {
        if (api && request.url === "/api/v1/config") {
          let body = "";
          upstream.on("data", (chunk) => (body += chunk));
          upstream.on("end", () => {
            try {
              response.writeHead(upstream.statusCode, {
                "Content-Type": "application/json",
              });
              response.end(
                JSON.stringify({ ...JSON.parse(body), proxied: true }),
              );
            } catch {
              response.writeHead(502);
              response.end("Backend unavailable");
            }
          });
        } else {
          response.writeHead(upstream.statusCode, upstream.headers);
          upstream.pipe(response);
        }
      },
    );
    proxy.on("error", () => {
      response.writeHead(502);
      response.end("Python server unavailable");
    });
    request.pipe(proxy);
  });
  server.on("upgrade", (request, socket, head) => {
    const upstream = net.connect(
      Number(process.env.AETHEL_DEV_WS_PORT ?? Number(backend.port || 80) + 1),
      backend.hostname,
      () => {
        const headers = {
          ...request.headers,
          host: `${backend.hostname}:${Number(backend.port || 80) + 1}`,
          origin: backend.origin,
        };
        upstream.write(
          `${request.method} ${request.url} HTTP/1.1\r\n${Object.entries(
            headers,
          )
            .map(([k, v]) => `${k}: ${v}`)
            .join("\r\n")}\r\n\r\n`,
        );
        upstream.write(head);
        socket.pipe(upstream);
        upstream.pipe(socket);
      },
    );
    upstream.on("error", () => socket.destroy());
    socket.on("error", () => upstream.destroy());
    socket.on("close", () => upstream.destroy());
  });
  server.listen(8082, "127.0.0.1", () =>
    process.stdout.write("Aethel development UI: http://127.0.0.1:8082\n"),
  );
}
