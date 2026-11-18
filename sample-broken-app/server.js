// Node server demonstrating JS endpoint and CORS
const express = require('express');
const app = express();

// Seeded CORS wildcard in Node
app.use((req, res, next) => {
    res.header('Access-Control-Allow-Origin', '*');
    next();
});

// Seeded env var missing from .env.example
const sessionSecret = process.env.NODE_SESSION_SECRET;

app.get('/api/v1/calculate', (req, res) => {
    res.json({ status: 'ok' });
});

module.exports = app;
