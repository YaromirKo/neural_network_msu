from loader import Loader
import tensorflow
import numpy
import datetime
import sys
from time import sleep
########################################################################################################################
path_dataset_train = './train/*'
path_save_weights = './'
loading_weights = (False, './w_', 0, 1)
########################################################################################################################
shape_img = (256, 256, 3)
# Configure data loader
loading_img = Loader(shape_img=(shape_img[0], shape_img[1]), path_data=path_dataset_train)
########################################################################################################################
target = tensorflow.keras.layers.Input(shape=shape_img)
in_img = tensorflow.keras.layers.Input(shape=shape_img)
optimizer = tensorflow.keras.optimizers.Adam(0.0002, 0.5)
# Number of filters in the first layer of G and D
generator_filters = 64
discriminator_filters = 64
########################################################################################################################


def discriminator_layers(layer_input, filtres, kernal, batch_normalization):
    layer = tensorflow.keras.layers.Conv2D(filtres, kernel_size=kernal, strides=2, padding='same')(layer_input)
    layer = tensorflow.keras.layers.LeakyReLU(alpha=0.2)(layer)
    if batch_normalization:
        layer = tensorflow.keras.layers.BatchNormalization(momentum=0.8)(layer)
    return layer


concatenate_layers = tensorflow.keras.layers.Concatenate(axis=-1)([target, in_img])
d1 = discriminator_layers(concatenate_layers, discriminator_filters,     kernal=4, batch_normalization=False)
d2 = discriminator_layers(d1,                 discriminator_filters * 2, kernal=4, batch_normalization=True)
d3 = discriminator_layers(d2,                 discriminator_filters * 4, kernal=4, batch_normalization=True)
d4 = discriminator_layers(d3,                 discriminator_filters * 8, kernal=4, batch_normalization=True)
validity = tensorflow.keras.layers.Conv2D(1, kernel_size=4, strides=1, padding='same')(d4)
DISCRIMINATOR = tensorflow.keras.models.Model([target, in_img], validity)
DISCRIMINATOR.compile(loss='mse', optimizer=optimizer, metrics=['accuracy'])

# U-Net Generator

def generator_layers_conv(layer_input, filters, kernal, batch_normalization):
    layer = tensorflow.keras.layers.Conv2D(filters, kernel_size=kernal, strides=2, padding='same')(layer_input)
    layer = tensorflow.keras.layers.LeakyReLU(alpha=0.2)(layer)
    if batch_normalization:
        layer = tensorflow.keras.layers.BatchNormalization(momentum=0.8)(layer)
    return layer


def generator_layers_deconv(layer_input, skip_layer_input, filters, kernal, dropout_rate=0):
    layer = tensorflow.keras.layers.UpSampling2D(size=2)(layer_input)
    layer = tensorflow.keras.layers.Conv2D(filters, kernel_size=kernal, strides=1, padding='same', activation='relu')(layer)
    if dropout_rate:
        layer = tensorflow.keras.layers.Dropout(dropout_rate)(layer)
    layer = tensorflow.keras.layers.BatchNormalization(momentum=0.8)(layer)
    layer = tensorflow.keras.layers.Concatenate()([layer, skip_layer_input])
    return layer


# Image input
image_input = tensorflow.keras.layers.Input(shape=shape_img)
# Downsampling
d1 = generator_layers_conv(image_input, generator_filters,     kernal=4, batch_normalization=False)
d2 = generator_layers_conv(d1,          generator_filters * 2, kernal=4, batch_normalization=True)
d3 = generator_layers_conv(d2,          generator_filters * 4, kernal=4, batch_normalization=True)
d4 = generator_layers_conv(d3,          generator_filters * 8, kernal=4, batch_normalization=True)
d5 = generator_layers_conv(d4,          generator_filters * 8, kernal=4, batch_normalization=True)
d6 = generator_layers_conv(d5,          generator_filters * 8, kernal=4, batch_normalization=True)
d7 = generator_layers_conv(d6,          generator_filters * 8, kernal=4, batch_normalization=True)
# Upsamplig
u1 = generator_layers_deconv(d7, d6, generator_filters,     kernal=4)
u2 = generator_layers_deconv(u1, d5, generator_filters * 8, kernal=4)
u3 = generator_layers_deconv(u2, d4, generator_filters * 8, kernal=4)
u4 = generator_layers_deconv(u3, d3, generator_filters * 8, kernal=4)
u5 = generator_layers_deconv(u4, d2, generator_filters * 4, kernal=4)
u6 = generator_layers_deconv(u5, d1, generator_filters * 2, kernal=4)
u7 = tensorflow.keras.layers.UpSampling2D(size=2)(u6)
fake_output_img = tensorflow.keras.layers.Conv2D(shape_img[2], kernel_size=4, strides=1, padding='same', activation='tanh')(u7)
GENERATOR = tensorflow.keras.models.Model(image_input, fake_output_img)

if loading_weights[0]:
    GENERATOR.load_weights(loading_weights[1])

fake_img_gen = GENERATOR(in_img)
# For the combined model we will only train the generator
DISCRIMINATOR.trainable = False
# Discriminators determines validity of translated images / condition pairs
valid = DISCRIMINATOR([fake_img_gen, in_img])
GAN = tensorflow.keras.models.Model(inputs=[target, in_img], outputs=[valid, fake_img_gen])
GAN.compile(loss=['mse', 'mae'], loss_weights=[1, 100], optimizer=optimizer)
########################################################################################################################





# train
epochs = 200
batch_size = 1
interval_gen_test = 50
# Calculate output shape of D (PatchGAN)
patch = int(shape_img[0] / 2 ** 4)
valid = numpy.ones((batch_size, ) + (patch, patch, 1))
fake = numpy.zeros((batch_size, ) + (patch, patch, 1))

start_time = datetime.datetime.now()
for epoch in range(epochs):
    steps = 0
    for batch_index, (target, in_img) in enumerate(loading_img.load_img(batch_size=batch_size)):
        # ---------------------
        #  Train Discriminator
        # ---------------------
        # Condition on B and generate a translated version
        fake_img = GENERATOR.predict(in_img)
        # Train the discriminators (original images = real / generated = Fake)
        d_loss_real = DISCRIMINATOR.train_on_batch([target, in_img], valid)
        d_loss_fake = DISCRIMINATOR.train_on_batch([fake_img, in_img], fake)
        d_loss = 0.5 * numpy.add(d_loss_real, d_loss_fake)
        # -----------------
        #  Train Generator
        # -----------------
        # Train the generators
        g_loss = GAN.train_on_batch([target, in_img], [valid, target])
        elapsed_time = datetime.datetime.now() - start_time
        if batch_size % int((batch_size / 51) - 2):
            steps += 1
        sys.stdout.write('\r')
        sys.stdout.write("[Epoch %d/%d] [%-51s] [Batch %d/%d] [D loss: %f, acc: %d%%] [G loss: %f] time: %s"
                         % (epoch + loading_weights[2], epochs, '=' * steps, batch_index, loading_img.batch_num, d_loss[0], 100*d_loss[1], g_loss[0], elapsed_time))
        sys.stdout.flush()
        sleep(0.25)

