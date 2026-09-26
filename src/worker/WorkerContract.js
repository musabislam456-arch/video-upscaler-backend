/**
 * Worker contract.
 *
 * A future worker must implement:
 *   await run({ job, inputPath, outputPath, updateProgress, signal })
 * and return:
 *   { outputPath }
 *
 * updateProgress({ progress, status }) must use progress 0..100.
 *
 * The backend intentionally does not assume Python, FFmpeg, OpenCV, a GPU,
 * or any particular upscaling algorithm here.
 */
export class WorkerContract {
  async run() {
    throw new Error("WorkerContract.run() must be implemented.");
  }
}
