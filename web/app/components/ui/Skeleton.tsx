export function Skeleton({ w, h }: { w?: string; h?: number }) {
  return <span className="skeleton" style={{ display: "block", width: w || "60%", height: h || 20 }} />;
}

export default Skeleton;
