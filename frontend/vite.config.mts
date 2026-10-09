import {defineConfig} from 'vite';
import react from '@vitejs/plugin-react';
import {resolve,dirname} from 'node:path';
import {fileURLToPath} from 'node:url';
export default defineConfig({root:resolve(dirname(fileURLToPath(import.meta.url))),base:'./',plugins:[react()],build:{outDir:'dist',emptyOutDir:true},server:{host:'127.0.0.1',port:5173,strictPort:true}});
