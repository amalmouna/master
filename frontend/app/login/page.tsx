import { LoginForm } from "@/components/auth/LoginForm";

export default async function LoginPage({
  searchParams,
}: {
  searchParams: Promise<{ next?: string }>;
}) {
  const { next } = await searchParams;

  return (
    <div className="flex min-h-screen items-center justify-center bg-background px-4">
      <div className="w-full max-w-sm rounded-lg border border-border bg-surface p-6">
        <h1 className="text-base font-semibold text-foreground">Analyse pédagogique</h1>
        <p className="mt-1 text-xs text-muted-foreground">
          Accès réservé à l&apos;administration de l&apos;établissement.
        </p>
        <div className="mt-4">
          <LoginForm next={next ?? "/"} />
        </div>
      </div>
    </div>
  );
}
