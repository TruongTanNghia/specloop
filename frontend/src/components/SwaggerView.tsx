import SwaggerUI from "swagger-ui-react";
import "swagger-ui-react/swagger-ui.css";

export default function SwaggerView({ spec }: { spec: object }) {
  return (
    <div className="swagger-box">
      <SwaggerUI spec={spec} docExpansion="list" defaultModelsExpandDepth={0} supportedSubmitMethods={[]} />
    </div>
  );
}
