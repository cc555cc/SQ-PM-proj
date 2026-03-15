FROM rust:1.88-bookworm AS builder

WORKDIR /app
COPY . .

RUN apt-get update && apt-get install -y pkg-config libssl-dev && rm -rf /var/lib/apt/lists/*
RUN cargo build --release

FROM debian:bookworm-slim

RUN apt-get update && apt-get install -y ca-certificates libssl3 && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY --from=builder /app/target/release/opensovd-cda /usr/local/bin/opensovd-cda
COPY ./opensovd-cda.toml /app/opensovd-cda.toml

EXPOSE 20002

CMD ["opensovd-cda"]