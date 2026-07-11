import Link from "next/link";

export default function Navbar() {
  return (
    <nav className="w-full border-b px-8 py-4 flex items-center justify-between">
      <Link href="/" className="text-xl font-bold">
        TrailQ
      </Link>

      <div className="flex gap-6">
        <Link href="/trails">Explore Trails</Link>

        <Link href="/saved">Saved</Link>

        <Link href="/login">Login</Link>
      </div>
    </nav>
  );
}
