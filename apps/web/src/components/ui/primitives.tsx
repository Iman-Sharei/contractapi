"use client";

import Link from "next/link";
import type { AnchorHTMLAttributes, ButtonHTMLAttributes, HTMLAttributes, InputHTMLAttributes, ReactNode } from "react";
import { Icon, type IconName } from "./Icon";
import ui from "./ui.module.css";

export function cx(...names: (string | false | null | undefined)[]) {
  return names.filter(Boolean).join(" ");
}

export type Variant = "primary" | "secondary" | "ghost" | "danger";
export type Size = "sm" | "md" | "lg";
export type Tone = "neutral" | "success" | "warning" | "danger" | "accent";

export function buttonClass(variant: Variant = "secondary", size: Size = "md", iconOnly = false) {
  return cx(ui.btn, ui[variant], size !== "md" && ui[size], iconOnly && ui.iconOnly);
}

type ButtonProps = ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: Variant;
  size?: Size;
  icon?: IconName;
  busy?: boolean;
};

export function Button({ variant, size, icon, busy, className, children, type = "button", ...rest }: ButtonProps) {
  return (
    <button type={type} className={cx(buttonClass(variant, size, !children), className)} {...rest}>
      {busy ? <span className={ui.spinner} aria-hidden /> : icon && <Icon name={icon} size={size === "sm" ? 14 : 16} />}
      {children}
    </button>
  );
}

type LinkProps = AnchorHTMLAttributes<HTMLAnchorElement> & {
  href: string;
  variant?: Variant;
  size?: Size;
  icon?: IconName;
  /** Opens in a new tab (docs, live API). */
  external?: boolean;
};

export function ButtonLink({ href, variant, size, icon, external, className, children, ...rest }: LinkProps) {
  const cls = cx(buttonClass(variant, size, !children), className);
  const inner = (
    <>
      {icon && <Icon name={icon} size={size === "sm" ? 14 : 16} />}
      {children}
      {external && <Icon name="external" size={13} />}
    </>
  );
  return external ? (
    <a href={href} className={cls} target="_blank" rel="noreferrer" {...rest}>
      {inner}
    </a>
  ) : (
    <Link href={href} className={cls} {...rest}>
      {inner}
    </Link>
  );
}

export function Badge({
  tone = "neutral",
  dot,
  pulse,
  className,
  children,
  ...rest
}: HTMLAttributes<HTMLSpanElement> & { tone?: Tone; dot?: boolean; pulse?: boolean }) {
  return (
    <span className={cx(ui.badge, tone !== "neutral" && ui[`tone-${tone}`], className)} {...rest}>
      {dot && <span className={cx(ui.dot, pulse && ui.pulse)} aria-hidden />}
      {children}
    </span>
  );
}

export function Card({
  className,
  pad,
  children,
  ...rest
}: HTMLAttributes<HTMLElement> & { pad?: boolean }) {
  return (
    <section className={cx(ui.card, pad && ui.cardPad, className)} {...rest}>
      {children}
    </section>
  );
}

export function CardHeader({
  title,
  description,
  icon,
  actions,
  id,
}: {
  title: ReactNode;
  description?: ReactNode;
  icon?: IconName;
  actions?: ReactNode;
  id?: string;
}) {
  return (
    <div className={ui.cardHeader}>
      <div className={ui.cardTitleRow}>
        {icon && (
          <span className={ui.cardIcon}>
            <Icon name={icon} size={17} />
          </span>
        )}
        <div style={{ minWidth: 0 }}>
          <h2 className={ui.cardTitle} id={id}>
            {title}
          </h2>
          {description && <p className={ui.cardDesc}>{description}</p>}
        </div>
      </div>
      {actions && <div className={ui.actions}>{actions}</div>}
    </div>
  );
}

export function CardBody({ className, children, ...rest }: HTMLAttributes<HTMLDivElement>) {
  return (
    <div className={cx(ui.cardBody, className)} {...rest}>
      {children}
    </div>
  );
}

const BANNER_ICON: Record<Tone, IconName> = {
  neutral: "info",
  accent: "info",
  success: "checkCircle",
  warning: "alert",
  danger: "alert",
};

export function Banner({
  tone = "accent",
  onDismiss,
  className,
  children,
  role,
  ...rest
}: HTMLAttributes<HTMLDivElement> & { tone?: Tone; onDismiss?: () => void }) {
  return (
    <div
      className={cx(ui.banner, ui[`tone-${tone}`], className)}
      role={role ?? (tone === "danger" ? "alert" : "status")}
      {...rest}
    >
      <Icon name={BANNER_ICON[tone]} size={17} />
      <div className={ui.bannerText}>{children}</div>
      {onDismiss && (
        <button type="button" className={ui.bannerClose} onClick={onDismiss} aria-label="Dismiss">
          <Icon name="x" size={14} />
        </button>
      )}
    </div>
  );
}

export function PageHeader({
  eyebrow,
  title,
  description,
  actions,
}: {
  eyebrow?: ReactNode;
  title: ReactNode;
  description?: ReactNode;
  actions?: ReactNode;
}) {
  return (
    <header className={ui.pageHeader}>
      <div className={ui.pageHeaderText}>
        {eyebrow && <div className={ui.eyebrow}>{eyebrow}</div>}
        <h1 className={ui.pageTitle}>{title}</h1>
        {description && <p className={ui.pageDesc}>{description}</p>}
      </div>
      {actions && <div className={ui.actions}>{actions}</div>}
    </header>
  );
}

export function EmptyState({
  icon = "sparkles",
  title,
  children,
  action,
}: {
  icon?: IconName;
  title: ReactNode;
  children?: ReactNode;
  action?: ReactNode;
}) {
  return (
    <div className={ui.empty}>
      <span className={ui.emptyIcon}>
        <Icon name={icon} size={22} />
      </span>
      <h2 className={ui.emptyTitle}>{title}</h2>
      {children && <p>{children}</p>}
      {action}
    </div>
  );
}

export type TabItem<T extends string> = { id: T; label: ReactNode; count?: number; icon?: IconName };

export function Tabs<T extends string>({
  items,
  value,
  onChange,
  label,
  variant = "underline",
  className,
}: {
  items: TabItem<T>[];
  value: T;
  onChange: (id: T) => void;
  label: string;
  variant?: "underline" | "segmented";
  className?: string;
}) {
  const seg = variant === "segmented";
  return (
    <div role="tablist" aria-label={label} className={cx(seg ? ui.segmented : ui.tabs, className)}>
      {items.map((t) => (
        <button
          key={t.id}
          type="button"
          role="tab"
          aria-selected={t.id === value}
          className={seg ? ui.segment : ui.tab}
          onClick={() => onChange(t.id)}
        >
          {t.icon && <Icon name={t.icon} size={15} />}
          {t.label}
          {t.count !== undefined && <span className={ui.tabCount}>{t.count}</span>}
        </button>
      ))}
    </div>
  );
}

/** A real checkbox drawn as a switch: keeps native keyboard, form and test behaviour. */
export function Switch({
  label,
  description,
  className,
  ...input
}: Omit<InputHTMLAttributes<HTMLInputElement>, "type"> & { label: ReactNode; description?: ReactNode }) {
  return (
    <label className={cx(ui.switchRow, className)}>
      <input type="checkbox" className={ui.switch} {...input} />
      <span className={ui.switchText}>
        <span className={ui.switchLabel}>{label}</span>
        {description && <span className={ui.hint}>{description}</span>}
      </span>
    </label>
  );
}

export function Method({ method }: { method: string }) {
  return <span className={cx(ui.method, ui[`method-${method}`])}>{method}</span>;
}

export function Hint({ children, className, ...rest }: HTMLAttributes<HTMLSpanElement>) {
  return (
    <span className={cx(ui.hint, className)} {...rest}>
      {children}
    </span>
  );
}

export { ui };
