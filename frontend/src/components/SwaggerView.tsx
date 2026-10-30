import SwaggerUI from "swagger-ui-react";
import "swagger-ui-react/swagger-ui.css";

// Swagger UI chỉ có giao diện sáng → lớp trong đảo màu, lớp ngoài giữ viền theo theme.
export default function SwaggerView({ spec }: { spec: object }) {
  return (
    <div className="swagger-box">
      <div className="swagger-inv">
        <SwaggerUI spec={spec} docExpansion="list" defaultModelsExpandDepth={0} supportedSubmitMethods={[]} />
      </div>
    </div>
  );
}
