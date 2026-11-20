import type { Metadata } from "next";
import PostPage from "./PostPage";

type Props = { params: Promise<{ id: string }> };

// A post's page is personal (what the reader may see), so it's never indexed.
export const metadata: Metadata = { title: "Post", robots: { index: false } };

export default async function ActivityPostPage({ params }: Props) {
  const { id } = await params;
  return <PostPage id={id} />;
}
