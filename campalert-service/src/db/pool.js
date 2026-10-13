"use strict";

// Loaded here, not just at each entrypoint: createPool() below reads
// process.env.* synchronously at module-load time, so if some other file
// requires this before it's called dotenv.config() itself (e.g.
// catalogSync.js requiring this at the top of the file, ahead of its own
// CLI-runner dotenv call), the pool would silently get created with
// undefined credentials. dotenv.config() is safe to call more than once.
require("dotenv").config();
const mysql = require("mysql2/promise");

const pool = mysql.createPool({
  host: process.env.MYSQL_HOST,
  port: Number(process.env.MYSQL_PORT ?? 3306),
  database: process.env.MYSQL_DATABASE,
  user: process.env.MYSQL_USER,
  password: process.env.MYSQL_PASSWORD,
  waitForConnections: true,
  connectionLimit: 10,
});

module.exports = pool;
