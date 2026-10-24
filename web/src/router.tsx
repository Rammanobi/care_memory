import { createBrowserRouter, Navigate, Outlet } from "react-router-dom";
import { CareProvider } from "./api/CareProvider";
import { DoctorShell } from "./components/DoctorShell";
import { LangProvider } from "./components/i18n";
import { RequireRole } from "./auth/session";
import Login from "./pages/Login";
import { Ask, Home, Me, Record } from "./pages/PatientApp";
import { PatientShell } from "./pages/PatientApp/Shell";
import Welcome from "./pages/PatientApp/Welcome";
import Messages from "./pages/PatientApp/Messages";
import { Help, Privacy } from "./pages/PatientApp/Me";
import SupporterApp from "./pages/Supporter";
import PatientsPage from "./pages/Patients";
import ApprovalsPage from "./pages/ReviewQueue";
import RequestsPage from "./pages/ReviewQueue/Requests";
import TodayPage from "./pages/Today";
import PatientPage from "./pages/Patient/PatientPage";
import AskPage from "./pages/Ask";
import LensPage from "./pages/Lens";
import DistrictPage from "./pages/District";
import AdminPage from "./pages/Admin";
import SettingsPage from "./pages/Settings";
import MorePage from "./pages/More";

function Root() {
  return (
    <LangProvider>
      <CareProvider>
        <Outlet />
      </CareProvider>
    </LangProvider>
  );
}

export const router = createBrowserRouter([
  {
    element: <Root />,
    children: [
      { path: "/", element: <Login /> },
      {
        path: "/doctor",
        element: <RequireRole area="doctor"><DoctorShell /></RequireRole>,
        children: [
          { index: true, element: <PatientsPage /> },
          { path: "patients/:id", element: <PatientPage /> },
          { path: "approvals", element: <ApprovalsPage /> },
          { path: "requests", element: <RequestsPage /> },
          { path: "today", element: <TodayPage /> },
          { path: "ask", element: <AskPage /> },
          { path: "lens", element: <LensPage /> },
          { path: "district", element: <DistrictPage /> },
          { path: "admin", element: <AdminPage /> },
          { path: "settings", element: <SettingsPage /> },
          { path: "more", element: <MorePage /> },
        ],
      },
      {
        path: "/patient",
        element: <RequireRole area="patient"><PatientShell /></RequireRole>,
        children: [
          { index: true, element: <Home /> },
          { path: "record", element: <Record /> },
          { path: "ask", element: <Ask /> },
          { path: "messages", element: <Messages /> },
          { path: "me", element: <Me /> },
          { path: "welcome", element: <Welcome /> },
          { path: "help", element: <Help /> },
          { path: "privacy", element: <Privacy /> },
        ],
      },
      { path: "/supporter", element: <RequireRole area="supporter"><SupporterApp /></RequireRole> },
      { path: "*", element: <Navigate to="/" replace /> },
    ],
  },
]);
