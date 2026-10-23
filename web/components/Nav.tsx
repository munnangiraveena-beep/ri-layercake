"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

const TABS = [
  ["/", "Playground"],
  ["/how-to-use/", "How to use"],
  ["/formulas/", "Formulas"],
  ["/contact/", "Contact"],
] as const;

export default function Nav() {
  const path = usePathname();
  return (
    <nav aria-label="Main">
      <ul className="tabs">
        {TABS.map(([href, label]) => {
          const on = href === "/" ? path === "/" : path?.startsWith(href.replace(/\/$/, ""));
          return (
            <li key={href}>
              <Link href={href} prefetch={false} aria-current={on ? "page" : undefined} className={on ? "on" : undefined}>{label}</Link>
            </li>
          );
        })}
      </ul>
    </nav>
  );
}
