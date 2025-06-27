import { useQuery } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import OpenHands from "#/api/open-hands";
import { useConversationId } from "#/hooks/use-conversation-id";
import { I18nKey } from "#/i18n/declaration";
import { transformVSCodeUrl } from "#/utils/vscode-url-helper";
import { useRuntimeIsReady } from "#/hooks/use-runtime-is-ready";

// Define the return type for the VS Code URL query
interface CascadeUrlResult {
  url: string | null;
  error: string | null;
}

export const useCascadeUrl = () => {
  const { t } = useTranslation();
  const { conversationId } = useConversationId();
  const runtimeIsReady = useRuntimeIsReady();

  return useQuery<CascadeUrlResult>({
    queryKey: ["cascade_url", conversationId],
    queryFn: async () => {
      if (!conversationId) throw new Error("No conversation ID");
      const data = await OpenHands.getCascadeUrl(conversationId);
      if (data.cascade_url) {
        return {
          url: transformVSCodeUrl(data.cascade_url),
          // url: data.cascade_url,
          error: null,
        };
      }
      return {
        url: null,
        error: t(I18nKey.CASCADE$URL_NOT_AVAILABLE),
      };
    },
    enabled: runtimeIsReady && !!conversationId,
    refetchOnMount: true,
    retry: 3,
  });
};
