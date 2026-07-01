"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { api, ApiError } from "@/lib/api";

export default function AuthGate({ children }: { children: React.ReactNode }) {
  const [checked, setChecked] = useState(false);
  const router = useRouter();

  useEffect(() => {
    api
      .summary()
      .then(() => setChecked(true))
      .catch((err) => {
        if (err instanceof ApiError && err.status === 401) {
          router.push("/login");
        } else {
          setChecked(true); // backend reachable issues shouldn't trap the user on a blank screen
        }
      });
  }, [router]);

  if (!checked) {
    return <div className="flex min-h-screen items-center justify-center bg-zinc-950 text-zinc-400">Loading...</div>;
  }
  return <>{children}</>;
}
