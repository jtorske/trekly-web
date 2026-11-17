import { redirect } from "next/navigation";

/** Reports are part of the moderation queue now. */
export default function AdminReportsPage() {
  redirect("/admin/moderation");
}
