import { Bounds, OrbitControls, useGLTF } from '@react-three/drei'
import { Canvas } from '@react-three/fiber'
import { Suspense } from 'react'

function PlushModel({ url }: { url: string }) {
  const { scene } = useGLTF(url)
  return <primitive object={scene} dispose={null} />
}

export function ModelViewer({ url }: { url: string }) {
  return (
    <div className="model-canvas" aria-label="Interactive normalized 3D model">
      <Canvas
        camera={{ fov: 38, position: [2.8, 1.8, 3.6] }}
        dpr={[1, 1.5]}
        gl={{ antialias: true, alpha: false }}
      >
        <color attach="background" args={['#eef0ec']} />
        <ambientLight intensity={1.8} />
        <directionalLight position={[4, 6, 5]} intensity={3.2} />
        <directionalLight position={[-4, 2, -3]} intensity={1.2} />
        <Suspense fallback={null}>
          <Bounds fit clip observe margin={1.25}>
            <PlushModel url={url} />
          </Bounds>
        </Suspense>
        <OrbitControls makeDefault enablePan={false} minDistance={1} maxDistance={12} />
      </Canvas>
    </div>
  )
}