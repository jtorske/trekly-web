import { redirect } from "next/navigation";

/** Profile moderation moved into the admin area's users table (and each user's page). */
export default function AdminProfilesRedirect() {
  redirect("/admin/users?filter=hidden");
}
