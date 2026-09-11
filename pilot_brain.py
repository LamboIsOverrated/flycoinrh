"""Measured fly circuitry, with an explicitly artificial economic interface.

The connectome does not understand currency. Economic observations are rendered
as luminance inputs. Descending neuron activity selects actions through a human-
designed mapping; changes in marked paper wealth provide an artificial reward.
"""
import copy
from io import BytesIO
from pathlib import Path
import numpy as np
from PIL import Image, ImageDraw
from flysim import FlyBrain
from flyeye import FlyEye, FlyPilot
from mushroom import MushroomBody

ROOT = Path(__file__).parent

class PersistentBrain(FlyBrain):
    def __init__(self, shared):
        self.__dict__ = shared.__dict__.copy()
        self.wdata = shared.wdata.copy()
        self.neural_state = {}

    def run(self, *args, **kwargs):
        kwargs['state'] = self.neural_state
        return super().run(*args, **kwargs)

class IsolatedLearning(MushroomBody):
    def load(self):
        return False  # No shared/global learning files; restored by the journal.

    def save(self):
        raise RuntimeError('Use the atomic pilot checkpoint')

    def __init__(self, brain):
        super().__init__(brain)
        # W is [postsynaptic, presynaptic]. Read actual input to each MBON.
        pam = brain.where(type_re='^PAM')
        ppl = brain.where(type_re='^PPL1')
        reward = np.abs(np.asarray(brain.W[self.mbon][:,pam].sum(axis=1)).ravel())
        punish = np.abs(np.asarray(brain.W[self.mbon][:,ppl].sum(axis=1)).ravel())
        self.reward_side = self.mbon[reward > punish]
        self.punish_side = self.mbon[punish > reward]
        side = np.zeros(brain.n,dtype=np.int8)
        side[self.reward_side],side[self.punish_side] = 1,-1
        self.side = side[self.post]

class BrainGarden:
    def __init__(self):
        shared = FlyBrain(ROOT/'build'/'graph.npz')
        self.neurons, self.edges = shared.n, len(shared.wdata)
        eye = FlyEye(shared, str(ROOT/'data'/'body-annotations.feather'))
        template = FlyPilot(shared, eye=eye, sim_steps=100)
        self.agents = []
        for i in range(10):
            brain = PersistentBrain(shared)
            pilot = copy.copy(template)
            pilot.fb = brain
            self.agents.append((brain,pilot,IsolatedLearning(brain)))

    def decide(self, i, observation, tick):
        brain,pilot,learning = self.agents[i]
        img = Image.new('L',(320,240),10)
        draw = ImageDraw.Draw(img)
        # Five economic signals with explicit scales, independent of any webpage.
        signals = [observation['cash_fraction'], observation['own_inventory']/15,
                   observation['input_inventory']/4, observation['margin'], observation['token_exposure']/.5]
        for j,value in enumerate(signals):
            shade=int(30+220*max(0,min(1,value)))
            draw.rectangle((j*64+3,30,j*64+59,210),fill=shade)
        learning.apply()
        dx,dy,click,hz,info = pilot.step(np.asarray(img,dtype=np.float32)/255,160,120,seed=tick*100+i,detail=True)
        learning.observe(info['fired'])
        # Artificial action mapping, not a claim about financial cognition.
        if click or hz['steer_L'] > hz['steer_R']:
            action='buy_input'
        elif hz['steer_R'] > hz['steer_L']:
            action='inspect_market'
        else:
            action='produce'
        telemetry={k:info[k] for k in ['firing','spikes_per_sec','mean_mv','visual','motor']}
        telemetry.update({'action':action,'motor_hz':hz,'neurons':brain.n,'learning':learning.stats(),
                          'decision_source':'connectome + explicit economic mapping'})
        return action,telemetry

    def reward(self,i,delta):
        learning=self.agents[i][2]
        if delta:
            learning.dopamine(1 if delta>0 else -1,min(1,abs(delta)*10000))
        learning.forget()

    def checkpoint(self,i):
        brain,_,learning=self.agents[i]
        out=BytesIO()
        np.savez_compressed(out,**brain.neural_state,gain=learning.gain,trace=learning.trace,
                            pos=learning.pos,events=np.array([learning.events['reward'],learning.events['punish']]))
        return out.getvalue()

    def restore(self,i,blob):
        brain,_,learning=self.agents[i]
        with np.load(BytesIO(blob),allow_pickle=False) as data:
            if not np.array_equal(data['pos'],learning.pos):
                raise ValueError('Checkpoint connectome mismatch')
            for key in ('v','refr'):
                if key in data:
                    if data[key].shape != (brain.n,):raise ValueError('Checkpoint size mismatch')
                    brain.neural_state[key]=data[key].copy()
            learning.gain=data['gain'].copy();learning.trace=data['trace'].copy()
            learning.events={'reward':int(data['events'][0]),'punish':int(data['events'][1])}
