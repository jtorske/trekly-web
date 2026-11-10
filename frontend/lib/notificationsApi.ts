import { apiFetch } from "./api";
import type { NotificationList, NotificationPreferences } from "./notifications";

export const getNotifications = (signal?: AbortSignal) =>
  apiFetch<NotificationList>("/api/me/notifications", { auth: true, signal });

export const getUnreadCount = (signal?: AbortSignal) =>
  apiFetch<{ unread: number }>("/api/me/notifications/unread", { auth: true, signal });

/** Without ids, marks everything read. */
export const markNotificationsRead = (ids?: string[]) =>
  apiFetch<{ unread: number }>("/api/me/notifications/read", { method: "POST", body: ids ? { ids } : {}, auth: true });

export const getNotificationPreferences = (signal?: AbortSignal) =>
  apiFetch<NotificationPreferences>("/api/me/notification-settings", { auth: true, signal });

export const updateNotificationPreferences = (changes: Partial<NotificationPreferences>) =>
  apiFetch<NotificationPreferences>("/api/me/notification-settings", { method: "PATCH", body: changes, auth: true });
