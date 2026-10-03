"""Standalone optional runtime helper. Only local video and pinned models are used."""
import sys,json,os
from pathlib import Path
import cv2,numpy as np,mediapipe as mp
from PIL import Image

def main():
    source,models,out,fps=sys.argv[1:]; models=Path(models); out=Path(out); fps=float(fps)
    cv2.setNumThreads(2)
    vision=mp.tasks.vision; Base=mp.tasks.BaseOptions; mode=vision.RunningMode.VIDEO
    face=vision.FaceLandmarker.create_from_options(vision.FaceLandmarkerOptions(base_options=Base(model_asset_path=str(models/'face_landmarker.task')),running_mode=mode,num_faces=1,min_face_detection_confidence=.5,min_face_presence_confidence=.5,min_tracking_confidence=.5,output_facial_transformation_matrixes=True))
    segment=vision.ImageSegmenter.create_from_options(vision.ImageSegmenterOptions(base_options=Base(model_asset_path=str(models/'selfie_segmenter.tflite')),running_mode=mode,output_confidence_masks=True))
    capture=cv2.VideoCapture(source); total=max(1,int(capture.get(cv2.CAP_PROP_FRAME_COUNT))); records=[]; geometry=[]; meshes=[]; faces=people=0
    masks=out/'masks'; masks.mkdir(); indices=[33,263,10,152,234,454,1,13,159,386]
    try:
        while True:
            ok,frame=capture.read()
            if not ok:break
            number=len(records); image=mp.Image(image_format=mp.ImageFormat.SRGB,data=cv2.cvtColor(frame,cv2.COLOR_BGR2RGB)); timestamp=round(number*1000/fps)
            result=face.detect_for_video(image,timestamp); points=None; pose=None
            if result.face_landmarks:
                if len(result.face_landmarks[0]) != 478:
                    raise RuntimeError('This face model returned an unexpected landmark count.')
                points=[[result.face_landmarks[0][n].x,result.face_landmarks[0][n].y] for n in indices]; faces+=1
                matrix=result.facial_transformation_matrixes[0] if result.facial_transformation_matrixes else None
                pose={'points':[[result.face_landmarks[0][n].x,result.face_landmarks[0][n].y,result.face_landmarks[0][n].z] for n in indices],
                      'matrix':np.asarray(matrix).reshape(4,4).tolist() if matrix is not None else None}
                meshes.append(np.asarray([[p.x,p.y,p.z] for p in result.face_landmarks[0]],dtype=np.float16))
            else:
                meshes.append(np.full((478,3),np.nan,dtype=np.float16))
            segmentation=segment.segment_for_video(image,timestamp)
            mask=np.squeeze(segmentation.confidence_masks[-1].numpy_view())
            mask=np.clip((mask-.2)/.6,0,1)
            if (mask>.5).mean()>.02:people+=1
            Image.fromarray(np.uint8(mask*255)).resize((256,256),Image.Resampling.BILINEAR).save(masks/f'{number:08d}.png')
            records.append(points)
            geometry.append(pose)
            if number%10==0:print(f'KINETIC_PROGRESS {5+90*min(1,(number+1)/total):.1f} Analysing frame {number+1} / {total}',flush=True)
    finally:capture.release(); face.close(); segment.close()
    if not records:raise RuntimeError('No video frames could be read.')
    (out/'faces.json').write_text(json.dumps(records,separators=(',',':')))
    (out/'geometry.json').write_text(json.dumps(geometry,separators=(',',':')))
    np.save(out/'mesh.npy',np.stack(meshes))
    (out/'info.json').write_text(json.dumps({'frames':len(records),'face_frames':faces,'person_frames':people,'fps':fps}))
    print('KINETIC_PROGRESS 100 Analysis complete',flush=True)

if __name__=='__main__':main()
