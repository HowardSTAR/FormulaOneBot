const configuredOperator = import.meta.env.VITE_LEGAL_OPERATOR_NAME?.trim();
const configuredAddress = import.meta.env.VITE_LEGAL_OPERATOR_ADDRESS?.trim();
const configuredEmail = import.meta.env.VITE_LEGAL_CONTACT_EMAIL?.trim();
const configuredStorageLocation = import.meta.env.VITE_DATA_STORAGE_LOCATION?.trim();

export const legalConfig = {
  effectiveDate: "14 августа 2026 года",
  operatorName: configuredOperator || "администратор независимого проекта TurboTears",
  operatorAddress: configuredAddress || "предоставляется в ответ на юридически обоснованный запрос",
  contactEmail: configuredEmail || "",
  dataStorageLocation:
    configuredStorageLocation || "место размещения production-сервера, указанное оператором до запуска сервиса",
};

