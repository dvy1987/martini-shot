import { useMutation, useQueryClient } from "@tanstack/react-query";

import { decideApproval } from "@/api/endpoints";

export function useApproveMutation(approvalId: string) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: () => decideApproval(approvalId, "approve"),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: ["approvals"] });
    },
  });
}

export function useRejectMutation(approvalId: string) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: () => decideApproval(approvalId, "reject"),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: ["approvals"] });
    },
  });
}
