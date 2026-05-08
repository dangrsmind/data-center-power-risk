import { BrowserRouter, Routes, Route } from "react-router-dom";
import { Layout } from "./components/layout/Layout";
import { ProjectsPage } from "./pages/ProjectsPage";
import { ProjectDetailPage } from "./pages/ProjectDetailPage";
import { IngestPage } from "./pages/IngestPage";
import { MapPage } from "./pages/MapPage";
import { DiscoverPage } from "./pages/DiscoverPage";
import { CoordinatesPage } from "./pages/CoordinatesPage";

export function App() {
  return (
    <BrowserRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
      <Layout>
        <Routes>
          <Route path="/" element={<ProjectsPage />} />
          <Route path="/projects/:id" element={<ProjectDetailPage />} />
          <Route path="/ingest" element={<IngestPage />} />
          <Route path="/map" element={<MapPage />} />
          <Route path="/coordinates" element={<CoordinatesPage />} />
          <Route path="/discover" element={<DiscoverPage />} />
        </Routes>
      </Layout>
    </BrowserRouter>
  );
}
