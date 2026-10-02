/* 'server' = the FastAPI app serves these pages and the API (uvicorn src.serve.api:app).
   'browser' = static hosting: the models run in the visitor's browser (tools/build_static.py writes this file). */
window.PROHORI_MODE = window.PROHORI_MODE || 'server';
