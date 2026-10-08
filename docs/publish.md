# Publish the image

This page shows how to publish the image on GitHub Container Registry (GHCR). The arena pulls the image without a login. The image must be public.

Docker Hub works too. Use the same steps and the name `docker.io/YOUR-NAME/log-triage:v1`.

## Option A: publish from your computer

1. Create a GitHub token. The token needs the `write:packages` scope. Do not write the token in a file.

2. Log in to GHCR. Pass the token through standard input:

   ```sh
   echo "$GITHUB_TOKEN" | docker login ghcr.io -u NoeFlandre --password-stdin
   ```

3. Build and push the image:

   ```sh
   docker build --platform linux/amd64 -t ghcr.io/noeflandre/log-triage:v1 .
   docker push ghcr.io/noeflandre/log-triage:v1
   ```

## Option B: publish with GitHub Actions

The workflow `.github/workflows/image.yml` builds and pushes the image. It runs when you push a tag that starts with `v`, or when you start it by hand.

1. Push a tag:

   ```sh
   git tag v1
   git push origin v1
   ```

2. Open the **Actions** tab. Wait for the **Publish image** run to finish.

## Make the package public

A new GHCR package is private. Make it public before you submit.

1. Open `https://github.com/users/NoeFlandre/packages/container/log-triage`.
2. Open **Package settings**.
3. Open **Danger Zone**.
4. Select **Change visibility**, then **Public**.

## Check the public image

Log out, then pull the image. Your login must not be needed.

```sh
docker logout ghcr.io
docker pull ghcr.io/noeflandre/log-triage:v1
```

If the pull asks for a login, the package is still private. Repeat the visibility steps.
