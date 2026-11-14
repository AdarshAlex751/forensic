import { Route, Routes } from "react-router-dom";
import { pages, slots } from "./registry";
import { Layout } from "./shared/layout";
import { SlotsProvider } from "./shared/Slot";

export default function App() {
  return (
    <SlotsProvider value={slots}>
      <Layout>
        <Routes>
          {pages.map((p) => (
            <Route key={p.path} path={p.path} element={<p.component />} />
          ))}
        </Routes>
      </Layout>
    </SlotsProvider>
  );
}
