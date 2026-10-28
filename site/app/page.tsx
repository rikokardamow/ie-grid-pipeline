import { Dashboard } from "@/components/Dashboard";
import { loadReport } from "@/lib/report";

// Read once at build time: the static export holds the newest report's page.
export default function Page() {
  return <Dashboard report={loadReport()} />;
}
