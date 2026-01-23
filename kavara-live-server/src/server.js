
import http from 'node:http';
import fs from 'node:fs';
import path from 'node:path';
import { WebSocketServer } from 'ws';
import * as mime from 'mime-types'; // Changed import style just in case
import chokidar from 'chokidar';
import pc from 'picocolors';
import { fileURLToPath } from 'node:url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));

export function createServer(root, port) {
  const injectScript = fs.readFileSync(path.join(__dirname, 'inject.html'), 'utf-8');

  const server = http.createServer((req, res) => {
    // Handle WebSocket upgrade path check if needed, but 'ws' library handles upgrade.
    // If request comes here, it's a normal HTTP request.
    
    let filePath = path.join(root, req.url === '/' ? 'index.html' : req.url);
    
    // Prevent directory traversal
    if (!filePath.startsWith(root)) {
        res.writeHead(403);
        res.end('Forbidden');
        return;
    }

    fs.stat(filePath, (err, stats) => {
      if (err) {
        // If file not found, try adding .html or serving 404
        if (req.url !== '/' && !path.extname(req.url)) {
           const htmlPath = filePath + '.html';
           if (fs.existsSync(htmlPath)) {
               serveFile(htmlPath, res, injectScript);
               return;
           }
        }
        
        res.writeHead(404);
        res.end('Not Found');
        return;
      }

      if (stats.isDirectory()) {
        filePath = path.join(filePath, 'index.html');
        fs.stat(filePath, (err, stats) => {
            if (err || !stats.isFile()) {
                res.writeHead(404);
                res.end('Index not found');
                return;
            }
            serveFile(filePath, res, injectScript);
        });
      } else {
        serveFile(filePath, res, injectScript);
      }
    });
  });

  const wss = new WebSocketServer({ server, path: '/_kavara_live_reload' });

  // Watch for changes
  chokidar.watch(root, { ignoreInitial: true }).on('all', (event, path) => {
    // Debounce or just send?
    // sending immediately for simplicity
    wss.clients.forEach((client) => {
      if (client.readyState === 1) {
        client.send('reload');
      }
    });
  });

  server.listen(port, () => {
    console.log(pc.green(`\n  ➜  Local:   http://localhost:${port}/`));
    console.log(pc.dim(`  ➜  Serving: ${root}`));
    console.log(pc.dim(`  ➜  Press Ctrl+C to stop\n`));
  });
}

function serveFile(filePath, res, injectScript) {
  const ext = path.extname(filePath);
  let contentType = mime.contentType(ext) || 'application/octet-stream';
  
  // Custom fix for WASM if mime-types doesn't handle it (it usually does, but to be safe as per user request)
  if (ext === '.wasm') {
      contentType = 'application/wasm';
  }

  // Inject script into HTML
  if (contentType.includes('text/html')) {
    fs.readFile(filePath, 'utf-8', (err, content) => {
      if (err) {
        res.writeHead(500);
        res.end('Internal Server Error');
        return;
      }
      
      const injectedContent = content.replace('</body>', `${injectScript}</body>`);
      res.writeHead(200, { 'Content-Type': contentType });
      res.end(injectedContent);
    });
  } else {
    // Stream other files
    res.writeHead(200, { 'Content-Type': contentType });
    const stream = fs.createReadStream(filePath);
    stream.pipe(res);
  }
}
