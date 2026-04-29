import NextAuth from "next-auth";
import Google from "next-auth/providers/google";

const allowlist = (process.env.ADMIN_EMAILS ?? "")
  .split(",")
  .map((s) => s.trim().toLowerCase())
  .filter(Boolean);

function isAllowed(email: string | undefined | null) {
  if (!email) return false;
  return allowlist.includes(email.toLowerCase());
}

export const { handlers, auth, signIn, signOut } = NextAuth({
  providers: [Google],
  session: { strategy: "jwt", maxAge: 60 * 60 * 24 * 30 }, // 30일
  pages: { signIn: "/admin/login", error: "/admin/login" },
  callbacks: {
    async signIn({ user }) {
      // Google 로그인 시 이메일 allowlist 체크
      return isAllowed(user.email);
    },
    async jwt({ token, user }) {
      if (user?.email) token.email = user.email;
      return token;
    },
    async session({ session, token }) {
      if (token?.email && typeof token.email === "string") {
        session.user = { ...session.user, email: token.email };
      }
      return session;
    },
    async authorized({ auth: session }) {
      // proxy.ts 에서 사용 — 세션 + email allowlist 둘 다 통과해야 admin
      return Boolean(session?.user?.email && isAllowed(session.user.email));
    },
  },
});
