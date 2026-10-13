"use strict";

require("dotenv").config();
const { Queue } = require("bullmq");

const NOTIFICATIONS_QUEUE_NAME = "notifications";

const connection = {
  host: process.env.REDIS_HOST,
  port: Number(process.env.REDIS_PORT ?? 6379),
};

// BullMQ requires this on the Redis connection it manages.
const notificationsQueue = new Queue(NOTIFICATIONS_QUEUE_NAME, {
  connection: { ...connection, maxRetriesPerRequest: null },
});

module.exports = { notificationsQueue, connection, NOTIFICATIONS_QUEUE_NAME };
