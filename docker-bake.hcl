variable "PUSH" {
  default = "true"
}

variable "REPOSITORY" {
  default = "runpod"
}

variable "BASE_IMAGE_VERSION" {
  default = "preview"
}

group "all" {
  targets = ["main"]
}


group "main" {
  targets = ["worker-1210"]
}

 
target "worker-1210" {
  tags = ["${REPOSITORY}/worker-sglang:${BASE_IMAGE_VERSION}-cuda12.1.0"]
  context = "."
  dockerfile = "Dockerfile"
  args = {
    BASE_IMAGE_VERSION = "${BASE_IMAGE_VERSION}"
    WORKER_CUDA_VERSION = "12.1.0"
  }
  output = ["type=docker,push=${PUSH}"]
}