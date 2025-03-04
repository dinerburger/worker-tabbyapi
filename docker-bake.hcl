variable "PUSH" {
  default = "true"
}

variable "REPOSITORY" {
  default = "dinerburger"
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
  tags = ["${REPOSITORY}/worker-tabbyapi:${BASE_IMAGE_VERSION}"]
  context = "."
  dockerfile = "Dockerfile"
  args = {
    BASE_IMAGE_VERSION = "${BASE_IMAGE_VERSION}"
  }
  output = ["type=docker,push=${PUSH}"]
}