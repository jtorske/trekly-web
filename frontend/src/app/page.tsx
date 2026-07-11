import { api } from "@lib/api";

export default async function Home() {
  const res = await fetch(`${api}/`);

  const data = await res.json();

  return (
    <main>
      <h1>{data.message}</h1>
    </main>
  );
}
