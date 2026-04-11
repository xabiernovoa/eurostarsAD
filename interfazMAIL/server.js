const http = require('http');
const fs = require('fs');
const path = require('path');

const PORT = 3001;
const EMAIL_DIR = __dirname;
const EUROSTARS_IMAGES = '/home/xabier/Documentos/eurostars/images';

const MIME_TYPES = {
    '.html': 'text/html; charset=utf-8',
    '.css': 'text/css; charset=utf-8',
    '.js': 'application/javascript; charset=utf-8',
    '.json': 'application/json; charset=utf-8',
    '.jpeg': 'image/jpeg',
    '.jpg': 'image/jpeg',
    '.png': 'image/png',
    '.svg': 'image/svg+xml',
    '.ico': 'image/x-icon',
    '.woff2': 'font/woff2',
    '.woff': 'font/woff',
};

function getMime(filePath) {
    const ext = path.extname(filePath).toLowerCase();
    return MIME_TYPES[ext] || 'application/octet-stream';
}

function sendFile(res, filePath) {
    fs.readFile(filePath, (err, data) => {
        if (err) {
            res.writeHead(404);
            res.end('Not found');
            return;
        }
        res.writeHead(200, { 'Content-Type': getMime(filePath) });
        res.end(data);
    });
}

const server = http.createServer((req, res) => {
    const url = new URL(req.url, `http://localhost:${PORT}`);
    const pathname = decodeURIComponent(url.pathname);

    // CORS headers
    res.setHeader('Access-Control-Allow-Origin', '*');

    // API: list email HTML files
    if (pathname === '/api/emails') {
        const files = fs.readdirSync(EMAIL_DIR).filter(f => f.endsWith('.html') && f !== 'index.html');
        const emails = files.map((filename, idx) => {
            const content = fs.readFileSync(path.join(EMAIL_DIR, filename), 'utf-8');
            // Extract title from <title> tag
            const titleMatch = content.match(/<title>(.*?)<\/title>/i);
            const title = titleMatch ? titleMatch[1] : filename;
            // Extract preheader text
            const preheaderMatch = content.match(/<div[^>]*style="display:\s*none[^"]*"[^>]*>([\s\S]*?)<\/div>/i);
            const preheader = preheaderMatch ? preheaderMatch[1].trim() : '';
            // Determine type
            const isPostStay = filename.startsWith('post_stay');
            const type = isPostStay ? 'post_stay' : 'pre_arrival';
            // Extract ID
            const idMatch = filename.match(/(\d+)/);
            const id = idMatch ? idMatch[1] : String(idx);

            return { id, filename, title, preheader, type };
        });
        res.writeHead(200, { 'Content-Type': 'application/json' });
        res.end(JSON.stringify(emails));
        return;
    }

    // API: get email HTML content (rewrite image paths)
    if (pathname.startsWith('/api/email/')) {
        const filename = pathname.replace('/api/email/', '');
        const filePath = path.join(EMAIL_DIR, filename);
        if (!fs.existsSync(filePath)) {
            res.writeHead(404);
            res.end('Not found');
            return;
        }
        let content = fs.readFileSync(filePath, 'utf-8');
        // Rewrite absolute image paths to be served through our server
        content = content.replace(/src="\/home\/xabier\/Documentos\/eurostars\/images\//g, 'src="/images/eurostars/');
        res.writeHead(200, { 'Content-Type': 'text/html; charset=utf-8' });
        res.end(content);
        return;
    }

    // Serve eurostars images
    if (pathname.startsWith('/images/eurostars/')) {
        const imgPath = pathname.replace('/images/eurostars/', '');
        const filePath = path.join(EUROSTARS_IMAGES, imgPath);
        sendFile(res, filePath);
        return;
    }

    // Serve static files from EMAIL_DIR
    let filePath = pathname === '/' ? path.join(EMAIL_DIR, 'index.html') : path.join(EMAIL_DIR, pathname.slice(1));
    sendFile(res, filePath);
});

server.listen(PORT, () => {
    console.log(`\n  📧 Gmail Demo Server running at http://localhost:${PORT}\n`);
});
