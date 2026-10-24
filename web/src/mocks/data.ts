// Sample data. The doctor-side seed lives in seed.ts; the single-patient profile below feeds the patient app.
export { makeSeed, makeEmpty, usageFor } from "./seed";

export const patientProfile = {
  code: "PT-0142",
  name: "Ravi",
  streak: 12,
  clinic: "Anantapur Clinic",
  nextVisit: "Wed 6 pm",
  message: { from: "yesterday", text: "Please bring your medicine strip to the visit." },
  // 30-day history: 'o' taken, 'm' missed; the 30th cell is today
  history: "ooooooooooomoooooooooooooooooo",
  medicines: [
    { name: "Morning tablets", how: "Every day, with water" },
    { name: "Vitamin tablet", how: "Every day, evening" },
  ],
  upcoming: [
    { name: "Clinic visit", detail: "Wed 6 pm · Anantapur" },
    { name: "Lab test", detail: "Date will be shared by clinic" },
  ],
};
