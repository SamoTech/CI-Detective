# Central NVIDIA Execution

CI Detective provides a GitHub-native reusable workflow for NVIDIA enhanced analysis.

The workflow targets the `NVIDIA-CENTRAL` environment and reads `NVIDIA_API_KEY` from that environment. Consumer workflows provide deterministic evidence as an input; the NVIDIA credential is not supplied by the consumer.

The deterministic CI Detective diagnosis remains authoritative. NVIDIA is an enhanced reasoning layer and its failure must not replace deterministic evidence.

Consumer repositories can call the reusable workflow with `workflow_call` when their GitHub policy allows use of public reusable workflows. Pinning the called workflow to a reviewed commit SHA is preferred for production use.
