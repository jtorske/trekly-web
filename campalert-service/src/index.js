"use strict";

// Entrypoint stub — jobs (catalogSync, availabilityPoller, notifier) aren't
// wired in yet. This just confirms the container/env boots correctly so
// `docker-compose up` has something real to run while the rest of the
// service is still being built out.
require("dotenv").config();

const required = ["MYSQL_HOST", "MYSQL_DATABASE", "MYSQL_USER", "REDIS_HOST"];
const missing = required.filter((key) => !process.env[key]);
if (missing.length > 0) {
  console.error(`Missing required env vars: ${missing.join(", ")}`);
  process.exit(1);
}

console.log("CampAlert service scaffold booted. Jobs not yet wired in.");
console.log(`MySQL target: ${process.env.MYSQL_HOST}:${process.env.MYSQL_PORT ?? 3306}/${process.env.MYSQL_DATABASE}`);
console.log(`Redis target: ${process.env.REDIS_HOST}:${process.env.REDIS_PORT ?? 6379}`);
