import { auth, signOut } from "../../auth";

export default async function AdminLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const session = await auth();
  const email = session?.user?.email;

  return (
    <div>
      {email ? (
        <div className="flex items-center justify-end gap-3 border-b border-slate-200 bg-slate-50 px-6 py-2 text-xs text-slate-600">
          <span>{email}</span>
          <form
            action={async () => {
              "use server";
              await signOut({ redirectTo: "/admin/login" });
            }}
          >
            <button
              type="submit"
              className="rounded-md border border-slate-300 bg-white px-2 py-1 text-xs hover:bg-slate-100"
            >
              로그아웃
            </button>
          </form>
        </div>
      ) : null}
      {children}
    </div>
  );
}
