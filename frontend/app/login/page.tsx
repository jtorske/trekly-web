import { Suspense } from "react";
import LoginForm from "@/components/AuthForm";

export default function LoginPage() {
  return (
    <Suspense>
      <LoginForm />
    </Suspense>
  );
}
