#!/usr/bin/env node

import { Command } from 'commander';
import { createServer } from '../src/server.js';
import path from 'path';
import process from 'process';

const program = new Command();

program
  .name('kv')
  .description('A lightweight, modern CLI web server with live reload')
  .version('1.0.0')
  .argument('[dir]', 'root directory to serve', '.')
  .option('-p, --port <number>', 'port to use', '8080')
  .action((dir, options) => {
    const root = path.resolve(process.cwd(), dir);
    const port = parseInt(options.port, 10);
    createServer(root, port);
  });

program.parse();
