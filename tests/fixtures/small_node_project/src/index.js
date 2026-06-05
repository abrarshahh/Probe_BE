const express = require('express');

const app = express();

/**
 * Health check endpoint.
 */
app.get('/health', (req, res) => {
  res.json({ status: 'ok' });
});

/**
 * Start the server.
 */
function startServer(port = 3000) {
  app.listen(port, () => {
    console.log(`Server running on port ${port}`);
  });
}

module.exports = { app, startServer };
