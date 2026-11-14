import { Link } from "react-router-dom";

// Placeholder (Person 1): the walnut desk, closed folder and drop zone.
export function Desk() {
  return (
    <section>
      <h1 className="mb-2 text-xl">The desk</h1>
      <div className="rounded border-2 border-dashed border-stone-500 p-10 text-center">drop case folder here</div>
      <Link to="/summary" className="mt-4 inline-block underline">
        Open folder
      </Link>
    </section>
  );
}
