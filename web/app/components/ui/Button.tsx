import { forwardRef } from "react";

type Variant = "primary" | "secondary" | "danger" | "ghost";

interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant;
}

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(function Button(
  { variant = "secondary", className, style, ...props },
  ref
) {
  return (
    <button
      ref={ref}
      className={`ui-btn ui-btn--${variant}${className ? ` ${className}` : ""}`}
      style={style}
      {...props}
    />
  );
});

export default Button;
